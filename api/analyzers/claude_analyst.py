"""
VERITY — Claude 심층 분석 모듈 (2차 뇌)

Verity Brain이 상위로 분류한 종목만 Claude Sonnet에게 정밀 분석을 맡김.
Gemini의 1차 판정에 대한 '반론(Devil's Advocate)' 역할 수행.
"""
import json
import time
from typing import Dict, Optional

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


def _to_reco_score(rec: str) -> int:
    r = (rec or "").upper()
    if r in ("STRONG_BUY", "BUY", "매수", "강력매수", "강력 매수"):
        return 100
    if r in ("AVOID", "SELL", "회피", "매도"):
        return 0
    return 50


def _from_reco_score(score: float) -> str:
    if score >= 67:
        return "BUY"
    if score <= 33:
        return "AVOID"
    return "WATCH"


def _clip_int(x: float, lo: int = 0, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(x))))


def merge_dual_analysis(
    stock: dict,
    claude_result: dict,
    model_weights: Optional[Dict[str, float]] = None,
) -> dict:
    """
    Gemini + Claude 분석을 병합하여 최종 판정 생성.
    Claude가 override를 제시하면 최종 recommendation을 조정.
    """
    override = claude_result.get("override_recommendation")
    adj = int(claude_result.get("confidence_adjustment", 0) or 0)
    agrees = bool(claude_result.get("agrees_with_gemini", True))

    gemini_rec = stock.get("recommendation", "WATCH")
    gemini_conf = _clip_int(float(stock.get("confidence", 50) or 50))

    if override:
        claude_rec = override
    elif agrees:
        claude_rec = gemini_rec
    else:
        # 반론인데 override가 없으면 중립(WATCH)으로 완충
        claude_rec = "WATCH" if str(gemini_rec).upper() in ("BUY", "AVOID") else gemini_rec

    claude_conf = _clip_int(gemini_conf + adj)

    w = model_weights or {}
    wg = float(w.get("gemini", 0.55))
    wc = float(w.get("claude", 0.45))
    total_w = wg + wc
    if total_w <= 0:
        wg, wc, total_w = 0.55, 0.45, 1.0
    wg /= total_w
    wc /= total_w

    g_score = _to_reco_score(gemini_rec)
    c_score = _to_reco_score(claude_rec)
    consensus_score = (g_score * wg) + (c_score * wc)
    final_recommendation = _from_reco_score(consensus_score)
    final_confidence = _clip_int((gemini_conf * wg) + (claude_conf * wc))

    recommendation_gap = abs(g_score - c_score)
    manual_review_required = recommendation_gap >= 50 or (not agrees and abs(adj) >= 10)
    if recommendation_gap >= 60:
        conflict_level = "high"
    elif recommendation_gap >= 25 or (not agrees):
        conflict_level = "medium"
    else:
        conflict_level = "low"

    stock["recommendation"] = final_recommendation
    stock["confidence"] = final_confidence

    if override and final_recommendation != gemini_rec:
        stock["_recommendation_source"] = "claude_override"
    elif not agrees:
        stock["_recommendation_source"] = "gemini_disputed"
    else:
        stock["_recommendation_source"] = "gemini"

    hidden_risks = claude_result.get("hidden_risks", [])
    if hidden_risks:
        existing = stock.get("risk_flags", [])
        for r in hidden_risks:
            if r and r not in existing:
                existing.append(r)
        stock["risk_flags"] = existing

    stock["claude_analysis"] = {
        "verdict": claude_result.get("claude_verdict", ""),
        "agrees": agrees,
        "override": override,
        "confidence_adj": adj,
        "hidden_risks": hidden_risks,
        "hidden_opportunities": claude_result.get("hidden_opportunities", []),
        "vci_analysis": claude_result.get("vci_analysis", ""),
        "conviction_note": claude_result.get("conviction_note", ""),
    }
    stock["dual_consensus"] = {
        "gemini_recommendation": gemini_rec,
        "claude_recommendation": claude_rec,
        "final_recommendation": final_recommendation,
        "gemini_confidence": gemini_conf,
        "claude_confidence": claude_conf,
        "final_confidence": final_confidence,
        "weights": {"gemini": round(wg, 3), "claude": round(wc, 3)},
        "agreement": agrees,
        "conflict_level": conflict_level,
        "recommendation_gap": recommendation_gap,
        "manual_review_required": manual_review_required,
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


# ── Claude 풀가동 확장 ──────────────────────────────────────

_LIGHT_SYSTEM = """너는 한국 펀드매니저 보조역이다.
종목의 최신 데이터 변화를 보고 기존 판정을 유지할지 수정할지 빠르게 판단해라.
불필요한 서론 금지. JSON만 출력."""

_EMERGENCY_SYSTEM = """너는 급변 시황 전문 리스크 매니저다.
종목이 급등/급락한 원인을 추정하고, 보유자에게 즉각 대응 가이드를 줘라.
숫자 근거 필수. 서론 금지. JSON만."""

_MORNING_SYSTEM = """너는 15년 차 한국 펀드매니저다.
오늘 장 개장 전, 사장님에게 핵심 전략 포인트를 짧게 브리핑해라.
구체적 종목명+숫자로 뒷받침. 서론 금지. JSON만."""


def _call_claude(system: str, prompt: str, max_tokens: int = 400) -> Optional[dict]:
    """공통 Claude 호출 + JSON 파싱. 실패 시 None."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]
        result = json.loads(text)
        result["_input_tokens"] = message.usage.input_tokens
        result["_output_tokens"] = message.usage.output_tokens
        return result
    except (json.JSONDecodeError, anthropic.RateLimitError):
        return None
    except Exception:
        return None


def analyze_stock_light(stock: dict, prev_rec: str = "WATCH") -> Optional[dict]:
    """quick 모드용 경량 검증 — 기술+수급+Brain만으로 판정 변동 여부 확인."""
    tech = stock.get("technical", {})
    flow = stock.get("flow", {})
    mf = stock.get("multi_factor", {})
    brain = stock.get("verity_brain", {})
    vci = brain.get("vci", {})

    prompt = f"""[경량 판정 검증]
{stock.get('name', '?')} ({stock.get('ticker', '?')})
현재가 {stock.get('price', 0):,.0f}원 | PER {stock.get('per', 0):.1f}
직전 full 판정: {prev_rec}

[기술적] RSI {tech.get('rsi', '?')} | MACD {tech.get('macd_hist', '?')} | 추세 {tech.get('trend_strength', 0)} | {', '.join(tech.get('signals', [])[:3]) or '없음'}
[수급] {flow.get('flow_score', 50)}점 | 외국인 {flow.get('foreign_net', 0):+,}주 (5일 {flow.get('foreign_5d_sum', 0):+,}) | 기관 {flow.get('institution_net', 0):+,}주
[멀티팩터] {mf.get('multi_score', 0)}점 ({mf.get('grade', '?')})
[브레인] {brain.get('brain_score', '?')}점 ({brain.get('grade', '?')}) | VCI {vci.get('vci', 0):+d}

직전 full 때 "{prev_rec}" 판정이었다. 현재 데이터로 볼 때 판정을 바꿔야 하나?

JSON만:
{{"quick_verdict": "20자 이내 핵심", "alert_change": true/false, "new_recommendation": null 또는 "BUY"/"WATCH"/"AVOID", "confidence_delta": -15~+15, "watch_note": "주목할 변화 한 줄"}}"""

    return _call_claude(_LIGHT_SYSTEM, prompt, max_tokens=400)


def analyze_batch_light(
    stocks: list,
    prev_recs: dict,
) -> dict:
    """quick 모드: 여러 종목 경량 일괄 검증. prev_recs: ticker → 직전 recommendation."""
    results = {}
    for i, stock in enumerate(stocks):
        ticker = stock.get("ticker", "?")
        name = stock.get("name", "?")
        prev = prev_recs.get(ticker, "WATCH")
        if i > 0:
            time.sleep(1.5)
        print(f"    [Claude Light] ({i+1}/{len(stocks)}): {name}")
        result = analyze_stock_light(stock, prev)
        if result:
            results[ticker] = result
            changed = "변경" if result.get("alert_change") else "유지"
            new_r = result.get("new_recommendation")
            tag = f" → {new_r}" if new_r else ""
            tokens = result.get("_input_tokens", 0) + result.get("_output_tokens", 0)
            print(f"      {changed}{tag} | {result.get('quick_verdict', '')} | {tokens}tok")
        else:
            print(f"      스킵 (API 오류)")
    return results


def analyze_stock_emergency(
    stock: dict,
    price_change_pct: float,
    macro: Optional[dict] = None,
) -> Optional[dict]:
    """realtime 급변 종목 긴급 심사 — +-5% 이상 변동 시."""
    tech = stock.get("technical", {})
    flow = stock.get("flow", {})
    brain = stock.get("verity_brain", {})
    direction = "급등" if price_change_pct > 0 else "급락"

    macro_block = ""
    if macro:
        mood = macro.get("market_mood", {})
        macro_block = f"시장: {mood.get('label', '?')} ({mood.get('score', 0)}점) | VIX {macro.get('vix', {}).get('value', '?')}"

    prompt = f"""[긴급 심사] {stock.get('name', '?')} ({stock.get('ticker', '?')}) — {direction} {abs(price_change_pct):.1f}%
현재가 {stock.get('price', 0):,.0f}원
브레인: {brain.get('brain_score', '?')}점 ({brain.get('grade', '?')}) | 기존 판정: {stock.get('recommendation', 'WATCH')}
RSI {tech.get('rsi', '?')} | 수급 {flow.get('flow_score', 50)}점 | 외국인 {flow.get('foreign_net', 0):+,}주
{macro_block}

이 종목이 {direction} {abs(price_change_pct):.1f}%했다.
1) 원인 추정 2) 보유자 대응 제안

JSON만:
{{"cause_guess": "추정 원인 30자", "action": "대응 가이드 30자", "hold_or_exit": "HOLD" 또는 "EXIT" 또는 "ADD", "urgency_1_5": 정수, "reasoning": "근거 한 줄"}}"""

    return _call_claude(_EMERGENCY_SYSTEM, prompt, max_tokens=500)


def verify_tail_risk(headlines_text: str, gemini_severity: int) -> Optional[dict]:
    """꼬리위험 교차 검증 — Gemini severity 7+ 시 Claude에게도 판별 요청."""
    prompt = f"""다음 뉴스 헤드라인을 Gemini가 심각도 {gemini_severity}/10으로 판정했다.
네 판단은?

{headlines_text}

JSON만:
{{"severity_1_10": 정수, "category": "war/disaster/market_shock/geopolitics/irrelevant", "agrees_with_gemini": true/false, "summary_ko": "2문장 한국어 요약", "reasoning": "Gemini 판단에 동의/반대 근거 한 줄"}}"""

    system = "너는 지정학·재난 리스크 분석가다. 시장에 비선형 충격을 줄 수 있는 이벤트만 높은 심각도를 부여해라. 영화·게임·일상 보도는 irrelevant. JSON만 출력."
    return _call_claude(system, prompt, max_tokens=400)


def generate_morning_strategy(portfolio: dict) -> Optional[dict]:
    """full 분석 후 실행 — 다음 날 모닝 브리핑에 포함할 Claude 전략 코멘트."""
    daily = portfolio.get("daily_report", {})
    macro = portfolio.get("macro", {})
    mood = macro.get("market_mood", {})
    events = portfolio.get("global_events", [])
    recs = portfolio.get("recommendations", [])
    brain_data = portfolio.get("verity_brain", {})
    vams = portfolio.get("vams", {})

    top_picks = [
        r for r in recs
        if r.get("verity_brain", {}).get("brain_score", 0) >= 65
    ]
    top_picks.sort(key=lambda x: x.get("verity_brain", {}).get("brain_score", 0), reverse=True)
    top_names = [f"{r['name']}({r.get('verity_brain', {}).get('brain_score', 0)}점)" for r in top_picks[:5]]

    caution_picks = [
        r for r in recs
        if r.get("verity_brain", {}).get("grade") == "AVOID"
    ]
    caution_names = [r["name"] for r in caution_picks[:3]]

    upcoming = [e for e in events if (e.get("d_day") or 99) <= 3]
    event_lines = [f"D-{e['d_day']} {e['name']}" for e in upcoming[:4]]

    holdings = vams.get("holdings", [])
    holding_lines = [
        f"{h['name']} {h.get('return_pct', 0):+.1f}%"
        for h in holdings[:5]
    ]

    prompt = f"""[내일 장 전략 브리핑]
시장: {mood.get('label', '?')} ({mood.get('score', 0)}점)
VIX: {macro.get('vix', {}).get('value', '?')} | 환율: {macro.get('usd_krw', {}).get('value', '?')}
일일 요약: {daily.get('market_summary', '없음')[:200]}
전략: {daily.get('strategy', '없음')[:150]}

브레인 상위: {', '.join(top_names) or '없음'}
회피 종목: {', '.join(caution_names) or '없음'}
보유 현황: {', '.join(holding_lines) or '없음'}
임박 이벤트: {', '.join(event_lines) or '없음'}

내일 장에서 핵심 시나리오와 주목 포인트를 브리핑해라.

JSON만:
{{"scenario": "내일 시장 핵심 시나리오 1문장", "watch_points": ["주목 포인트 1", "주목 포인트 2"], "risk_note": "리스크 주의사항 1문장", "top_pick_comment": "브레인 상위 종목 중 내일 특히 주목할 종목과 이유 1문장"}}"""

    return _call_claude(_MORNING_SYSTEM, prompt, max_tokens=500)


def check_brain_drift(
    stock: dict,
    prev_brain_score: float,
    current_brain_score: float,
) -> Optional[dict]:
    """quick 모드: Brain 점수가 10점 이상 변동한 종목에 대해 원인 추정."""
    delta = current_brain_score - prev_brain_score
    direction = "상승" if delta > 0 else "하락"
    tech = stock.get("technical", {})
    flow = stock.get("flow", {})
    mf = stock.get("multi_factor", {})

    prompt = f"""[Brain 점수 급변 분석]
{stock.get('name', '?')} ({stock.get('ticker', '?')})
브레인: {prev_brain_score:.0f}점 → {current_brain_score:.0f}점 ({delta:+.0f}점 {direction})
현재가 {stock.get('price', 0):,.0f}원

RSI {tech.get('rsi', '?')} | 추세 {tech.get('trend_strength', 0)} | 시그널: {', '.join(tech.get('signals', [])[:3]) or '없음'}
수급: {flow.get('flow_score', 50)}점 | 외국인 {flow.get('foreign_net', 0):+,}주
멀티팩터: {mf.get('multi_score', 0)}점 ({mf.get('grade', '?')})

브레인 점수가 {abs(delta):.0f}점 {direction}한 원인과 대응을 분석해라.

JSON만:
{{"drift_cause": "원인 30자", "significance": "high/medium/low", "action_hint": "대응 제안 한 줄", "alert_worthy": true/false}}"""

    system = "너는 퀀트 리서치 분석가다. Brain score 변동 원인을 데이터로 추정해라. 서론 금지. JSON만."
    return _call_claude(system, prompt, max_tokens=400)
