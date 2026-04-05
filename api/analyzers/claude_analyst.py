"""
VERITY — Claude 심층 분석 모듈 (2차 뇌)

Verity Brain이 상위로 분류한 종목만 Claude Sonnet에게 정밀 분석을 맡김.
Gemini의 1차 판정에 대한 '반론(Devil's Advocate)' 역할 수행.
"""
import json
import time
from typing import Optional

import anthropic

from api.config import ANTHROPIC_API_KEY, DATA_DIR

_SYSTEM_PROMPT = """너는 15년 차 까칠한 한국 펀드매니저이자 리스크 심사역이다.

너의 역할은 1차 AI(Gemini)가 내린 판정에 대한 '반론 및 검증'이다.
Gemini가 "매수"라고 하면, 진짜 매수해도 되는지 숫자로 반박하거나 확인해라.
Gemini가 "회피"라고 하면, 혹시 시장이 과도하게 공포에 빠진 건 아닌지 역발상도 검토해라.

원칙:
- 숫자 없는 주장은 주장이 아니다
- 현금흐름과 부채를 무시하면 안 된다
- 컨센서스 대비 괴리가 15% 이상이면 반드시 언급
- VCI(팩트-심리 괴리)가 큰 종목은 왜 괴리가 생겼는지 추론
- 레드플래그가 있는데 매수 의견이면 반드시 재검토
- 반말 OK. 서론 금지. 핵심만."""


def init_claude() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _build_deep_prompt(stock: dict, gemini_result: dict, macro: Optional[dict] = None) -> str:
    """Gemini 1차 결과 + 원본 데이터를 합쳐 Claude 심층 분석 프롬프트 생성."""
    tech = stock.get("technical", {})
    sent = stock.get("sentiment", {})
    flow = stock.get("flow", {})
    mf = stock.get("multi_factor", {})
    pred = stock.get("prediction", {})
    bt = stock.get("backtest", {})
    brain = stock.get("verity_brain", {})
    cons = stock.get("consensus", {})
    dart = stock.get("dart_financials", {})
    cf = dart.get("cashflow", {})
    cm = stock.get("commodity_margin", {})

    # Gemini 1차 판정 요약
    gemini_verdict = gemini_result.get("ai_verdict", "분석 없음")
    gemini_rec = gemini_result.get("recommendation", "WATCH")
    gemini_conf = gemini_result.get("confidence", 0)
    gemini_gold = gemini_result.get("gold_insight", "")
    gemini_silver = gemini_result.get("silver_insight", "")
    gemini_risks = gemini_result.get("risk_flags", [])

    macro_block = ""
    if macro:
        mood = macro.get("market_mood", {})
        macro_block = f"""[매크로]
분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)
USD/KRW: {macro.get('usd_krw', {}).get('value', '?')}원
VIX: {macro.get('vix', {}).get('value', '?')}
미10Y: {macro.get('us_10y', {}).get('value', '?')}%"""

    cashflow_block = ""
    if cf.get("operating") or cf.get("free_cashflow"):
        fcf = cf.get("free_cashflow", 0)
        cashflow_block = f"""영업CF: {cf.get('operating', 0)/1e8:+,.0f}억 | 투자CF: {cf.get('investing', 0)/1e8:+,.0f}억 | 재무CF: {cf.get('financing', 0)/1e8:+,.0f}억
FCF: {fcf/1e8:+,.0f}억 {'⚠️ 현금 소진' if fcf < 0 else '✓ 현금 창출'}"""

    vci = brain.get("vci", {})
    rf = brain.get("red_flags", {})
    rf_lines = ""
    if rf.get("auto_avoid"):
        rf_lines += f"⛔ 자동회피: {'; '.join(rf['auto_avoid'])}\n"
    if rf.get("downgrade"):
        rf_lines += f"⚠️ 하향: {'; '.join(rf['downgrade'])}\n"

    cm_block = ""
    pr = (cm.get("primary") or {}) if isinstance(cm, dict) else {}
    if pr.get("commodity_ticker"):
        cm_block = f"""[원자재] {pr.get('commodity_ticker')} | r={pr.get('correlation_60d', '?')} | 마진안심 {pr.get('margin_safety_score', '?')}
국면: {pr.get('spread_regime', '?')} | 판가력 {pr.get('pricing_power', '?')} vs 원가변동성 {pr.get('raw_material_volatility_score', '?')}"""

    return f"""[종목 정밀 심사 요청]
{stock['name']} ({stock['ticker']}) | {stock.get('market', '')}
현재가 {stock.get('price', 0):,.0f}원 | 시총 {stock.get('market_cap', 0)/1e12:.1f}조
PER {stock.get('per', 0):.1f} | PBR {stock.get('pbr', 0):.2f} | 배당 {stock.get('div_yield', 0):.1f}%
고점대비 {stock.get('drop_from_high_pct', 0):.1f}% | 부채 {stock.get('debt_ratio', 0):.0f}% | 영업이익률 {stock.get('operating_margin', 0):.1f}% | ROE {stock.get('roe', 0):.1f}%
{cashflow_block}

[기술적] RSI {tech.get('rsi', '?')} | MACD {tech.get('macd_hist', '?')} | 볼린저 {tech.get('bb_position', '?')}% | 추세 {tech.get('trend_strength', 0)} | {', '.join(tech.get('signals', [])[:3]) or '시그널 없음'}
[뉴스] {sent.get('score', 50)}점 ({sent.get('headline_count', 0)}건) | 긍정 {sent.get('positive', 0)} / 부정 {sent.get('negative', 0)}
[수급] {flow.get('flow_score', 50)}점 | 외국인 {flow.get('foreign_net', 0):+,}주 (5일 {flow.get('foreign_5d_sum', 0):+,}) | 기관 {flow.get('institution_net', 0):+,}주
[컨센서스] {cons.get('consensus_score', '?')}점 ({cons.get('score_source', '?')}) | 목표가 괴리 {cons.get('upside_pct', 'N/A')}% | 영업이익 YoY {cons.get('operating_profit_yoy_est_pct', 'N/A')}%
[멀티팩터] {mf.get('multi_score', 0)}점 ({mf.get('grade', '?')})
[AI예측] XGBoost {pred.get('up_probability', '?')}% ({pred.get('method', '?')})
[백테스트] 승률 {bt.get('win_rate', 0)}% | 샤프 {bt.get('sharpe_ratio', 0)} | {bt.get('total_trades', 0)}회
{cm_block}
{macro_block}

[배리티 브레인] {brain.get('brain_score', '?')}점 | {brain.get('grade_label', '?')} ({brain.get('grade', '?')})
팩트 {brain.get('fact_score', {}).get('score', '?')} | 심리 {brain.get('sentiment_score', {}).get('score', '?')}
VCI: {vci.get('vci', '?'):+d} — {vci.get('label', '')}
{rf_lines}근거: {brain.get('reasoning', '')}

═══ Gemini 1차 판정 ═══
판정: {gemini_rec} (확신도: {gemini_conf})
근거: {gemini_verdict}
팩트: {gemini_gold}
센티: {gemini_silver}
리스크: {', '.join(gemini_risks) if gemini_risks else '없음'}

═══ 너의 임무 ═══
위 Gemini 판정을 검증하라. 동의하면 왜 동의하는지, 반대하면 어떤 숫자가 위험한지 명시.
Gemini가 놓친 것이 있으면 반드시 지적. VCI 괴리 원인 추론 필수.

JSON만:
{{
  "claude_verdict": "50자 이내. 핵심만. Gemini와 의견이 다르면 왜 다른지 명시",
  "agrees_with_gemini": true/false,
  "override_recommendation": null 또는 "BUY"/"WATCH"/"AVOID" (Gemini 판정 변경 시),
  "confidence_adjustment": -20~+20 (Gemini 확신도에 더하거나 빼는 보정치),
  "hidden_risks": ["Gemini가 놓친 리스크"],
  "hidden_opportunities": ["Gemini가 놓친 기회"],
  "vci_analysis": "VCI 괴리 원인 한 줄 추론",
  "conviction_note": "왜 이 종목에 확신이 있거나 없는지 한 줄"
}}"""


def analyze_stock_deep(stock: dict, gemini_result: dict, macro: Optional[dict] = None) -> dict:
    """단일 종목 Claude 심층 분석."""
    try:
        client = init_claude()
    except ValueError:
        return _empty_result("API 키 미설정")

    prompt = _build_deep_prompt(stock, gemini_result, macro)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)
        result["_model"] = "claude-sonnet-4"
        result["_input_tokens"] = message.usage.input_tokens
        result["_output_tokens"] = message.usage.output_tokens
        return result

    except json.JSONDecodeError:
        return _empty_result("JSON 파싱 실패")
    except anthropic.RateLimitError:
        return _empty_result("API 속도 제한")
    except Exception as e:
        return _empty_result(str(e)[:80])


def analyze_batch_deep(
    stocks: list[dict],
    gemini_results: dict[str, dict],
    macro: Optional[dict] = None,
) -> dict[str, dict]:
    """
    여러 종목 일괄 Claude 심층 분석.

    Args:
        stocks: 분석 대상 종목 리스트 (이미 Brain 필터링 완료)
        gemini_results: ticker → Gemini 분석 결과 맵
        macro: 매크로 지표

    Returns:
        ticker → Claude 분석 결과 맵
    """
    results = {}
    total = len(stocks)

    for i, stock in enumerate(stocks):
        ticker = stock.get("ticker", "?")
        name = stock.get("name", "?")
        gemini = gemini_results.get(ticker, {})

        if i > 0:
            time.sleep(2)

        print(f"    [Claude] ({i+1}/{total}): {name}")

        result = None
        for attempt in range(2):
            result = analyze_stock_deep(stock, gemini, macro)
            if result.get("_model"):
                break
            if "속도 제한" in result.get("_error", ""):
                wait = 20 * (attempt + 1)
                print(f"      ⏳ Claude 속도 제한 → {wait}초 대기")
                time.sleep(wait)

        results[ticker] = result
        tokens = result.get("_input_tokens", 0) + result.get("_output_tokens", 0)
        agrees = "동의" if result.get("agrees_with_gemini") else "반대"
        override = result.get("override_recommendation")
        override_tag = f" → {override}" if override else ""
        print(f"      {agrees}{override_tag} | 확신보정: {result.get('confidence_adjustment', 0):+d} | {tokens}토큰")

    return results


def merge_dual_analysis(stock: dict, claude_result: dict) -> dict:
    """
    Gemini + Claude 분석을 병합하여 최종 판정 생성.
    Claude가 override를 제시하면 최종 recommendation을 조정.
    """
    override = claude_result.get("override_recommendation")
    adj = claude_result.get("confidence_adjustment", 0)

    if override and override != stock.get("recommendation"):
        stock["recommendation"] = override
        stock["_recommendation_source"] = "claude_override"
    else:
        stock["_recommendation_source"] = "gemini" if claude_result.get("agrees_with_gemini") else "gemini_disputed"

    orig_conf = stock.get("confidence", 50)
    stock["confidence"] = max(0, min(100, orig_conf + adj))

    hidden_risks = claude_result.get("hidden_risks", [])
    if hidden_risks:
        existing = stock.get("risk_flags", [])
        for r in hidden_risks:
            if r and r not in existing:
                existing.append(r)
        stock["risk_flags"] = existing

    stock["claude_analysis"] = {
        "verdict": claude_result.get("claude_verdict", ""),
        "agrees": claude_result.get("agrees_with_gemini", True),
        "override": override,
        "confidence_adj": adj,
        "hidden_risks": hidden_risks,
        "hidden_opportunities": claude_result.get("hidden_opportunities", []),
        "vci_analysis": claude_result.get("vci_analysis", ""),
        "conviction_note": claude_result.get("conviction_note", ""),
    }

    return stock


def _empty_result(reason: str = "") -> dict:
    return {
        "claude_verdict": f"분석 스킵: {reason}" if reason else "분석 스킵",
        "agrees_with_gemini": True,
        "override_recommendation": None,
        "confidence_adjustment": 0,
        "hidden_risks": [],
        "hidden_opportunities": [],
        "vci_analysis": "",
        "conviction_note": "",
        "_error": reason,
    }
