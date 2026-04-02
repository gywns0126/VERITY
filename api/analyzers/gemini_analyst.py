"""
Gemini API 기반 최종 의사결정 모듈 (Sprint 2 강화)
- 멀티팩터 데이터 포함 프롬프트
- 매크로 컨텍스트 반영
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

    sent_headlines = sent.get("top_headlines", [])[:3]
    sent_detail_block = ""
    for h in sent.get("detail", [])[:3]:
        sent_detail_block += f"\n  [{h.get('label','?')}] {h.get('title','')}"

    return f"""당신은 한국 중소형주 전문 투자 분석가입니다.
주어진 데이터만을 근거로 분석하세요. 데이터에 없는 정보를 추측하거나 만들지 마세요.

[종목 정보]
- 종목명: {stock['name']} ({stock['ticker']}) / {stock['market']}
- 현재가: {stock['price']:,.0f}원 (전일 대비 {tech.get('price_change_pct', 0):+.1f}%)
- PER: {stock.get('per', 0):.1f} / PBR: {stock.get('pbr', 0):.2f}
- 배당수익률: {stock.get('div_yield', 0):.1f}%
- 52주 고점 대비: {stock.get('drop_from_high_pct', 0):.1f}%
- 시총: {stock.get('market_cap', 0)/1e12:.1f}조원 | 거래대금: {stock.get('trading_value', 0)/1e8:,.0f}억원
- 부채비율: {stock.get('debt_ratio', 0):.0f}% | 영업이익률: {stock.get('operating_margin', 0):.1f}% | ROE: {stock.get('roe', 0):.1f}%

[기술적 지표]
- RSI(14/Wilder): {tech.get('rsi', '?')} | MACD히스토그램: {tech.get('macd_hist', '?')}
- 볼린저 위치: {tech.get('bb_position', '?')}% | 거래량비: {tech.get('vol_ratio', '?')}x ({tech.get('vol_direction', '?')})
- 추세 강도: {tech.get('trend_strength', 0)} (-2=강한 하락 ~ +2=강한 상승)
- MA배열: 가격 {tech.get('price', 0):,.0f} > MA20 {tech.get('ma20', 0):,.0f} > MA60 {tech.get('ma60', 0):,.0f}
- 시그널: {', '.join(tech.get('signals', [])) or '없음'}

[뉴스 감성] ({sent.get('headline_count', 0)}건 분석)
- 점수: {sent.get('score', 50)}/100 (긍정 {sent.get('positive', 0)} / 부정 {sent.get('negative', 0)} / 중립 {sent.get('neutral', 0)})
- 주요 헤드라인:{sent_detail_block or ' 없음'}

[수급 동향] (점수: {flow.get('flow_score', 50)})
{flow_block}
- 외국인 지분율: {flow.get('foreign_ratio', 0):.1f}%

[멀티팩터 통합] {mf.get('multi_score', 0)}점 ({mf.get('grade', '?')})
- 기여도: {mf.get('factor_contribution', {{}})}
- 시그널: {', '.join(str(s) for s in mf.get('all_signals', [])[:5]) or '없음'}
{macro_block}
[AI 예측 모델]
- XGBoost 1주 상승확률: {pred.get('up_probability', '?')}% ({pred.get('method', '?')}, 정확도 {pred.get('model_accuracy', 0)}%)
- 주요 피처: {pred.get('top_features', {})}

[백테스트 결과] {f"(총 {bt['total_trades']}회 매매)" if bt.get('total_trades', 0) > 0 else '데이터 없음'}
- 승률: {bt.get('win_rate', 0)}% | 평균수익: {bt.get('avg_return', 0)}% | 최대낙폭: {bt.get('max_drawdown', 0)}%
- 샤프비율: {bt.get('sharpe_ratio', 0)} | 누적수익: {bt.get('total_return', 0)}%

중요: 아래 규칙을 반드시 지켜주세요.
1. gold_insight에는 반드시 구체적 수치를 포함 (PER, RSI, 부채비율 등)
2. recommendation은 멀티팩터 점수와 일관되게: ≥65 BUY, 45~64 WATCH, <45 AVOID
3. risk_flags는 실제 데이터에서 확인된 것만 기재
4. 추측이나 외부 정보를 사용하지 마세요

다음 JSON 형식으로만 답변하세요:
{{
  "ai_verdict": "50자 이내 종합의견 (반드시 데이터 수치 근거 포함)",
  "recommendation": "BUY" 또는 "WATCH" 또는 "AVOID",
  "risk_flags": ["데이터에서 확인된 리스크만"],
  "confidence": 0~100,
  "gold_insight": "재무/기술적 핵심 팩트 1줄 (구체적 수치 필수)",
  "silver_insight": "뉴스/수급/매크로 기반 참고 1줄"
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
