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

    macro_block = ""
    if macro:
        mood = macro.get("market_mood", {})
        macro_block = f"""
[매크로 환경]
- 시장 분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)
- USD/KRW: {macro.get('usd_krw', {}).get('value', '?')}원
- VIX: {macro.get('vix', {}).get('value', '?')}
- WTI: ${macro.get('wti_oil', {}).get('value', '?')}
- S&P500: {macro.get('sp500', {}).get('change_pct', 0):+.1f}%
"""

    return f"""당신은 한국 중소형주 전문 투자 분석가입니다. 아래 종합 데이터를 보고 분석해주세요.

[종목 정보]
- 종목명: {stock['name']} ({stock['ticker']}) / {stock['market']}
- 현재가: {stock['price']:,.0f}원
- PER: {stock.get('per', 0):.1f} / PBR: {stock.get('pbr', 0):.2f}
- 배당수익률: {stock.get('div_yield', 0):.1f}%
- 52주 고점 대비: {stock.get('drop_from_high_pct', 0):.1f}%
- 거래대금: {stock.get('trading_value', 0):,.0f}원

[기술적 지표]
- RSI(14): {tech.get('rsi', '?')}
- MACD: {tech.get('macd', '?')} (시그널: {tech.get('macd_signal', '?')})
- 볼린저밴드 위치: {tech.get('bb_position', '?')}% (하단=0%, 상단=100%)
- 거래량비: {tech.get('vol_ratio', '?')}배 (20일 평균 대비)
- 기술 시그널: {', '.join(tech.get('signals', [])) or '없음'}

[뉴스 감성]
- 감성 점수: {sent.get('score', 50)}/100 (긍정 {sent.get('positive', 0)} / 부정 {sent.get('negative', 0)})
- 최근 헤드라인: {' | '.join(sent.get('top_headlines', [])[:2]) or '없음'}

[수급 동향]
- 외국인: {'순매수' if flow.get('foreign_net', 0) > 0 else '순매도' if flow.get('foreign_net', 0) < 0 else '중립'}
- 기관: {'순매수' if flow.get('institution_net', 0) > 0 else '순매도' if flow.get('institution_net', 0) < 0 else '중립'}

[멀티팩터 점수]
- 종합: {mf.get('multi_score', 0)}점 ({mf.get('grade', '?')})
- 내역: 펀더멘털 {mf.get('factor_breakdown', {}).get('fundamental', 0)} / 기술 {mf.get('factor_breakdown', {}).get('technical', 0)} / 뉴스 {mf.get('factor_breakdown', {}).get('sentiment', 0)} / 수급 {mf.get('factor_breakdown', {}).get('flow', 0)} / 매크로 {mf.get('factor_breakdown', {}).get('macro', 0)}
{macro_block}
다음 JSON 형식으로만 답변하세요. 다른 텍스트 없이 JSON만 출력하세요:
{{
  "ai_verdict": "50자 이내의 종합 투자 의견 (데이터 근거 포함)",
  "recommendation": "BUY" 또는 "WATCH" 또는 "AVOID",
  "risk_flags": ["감지된 리스크가 있다면 여기에 나열"],
  "confidence": 0부터 100 사이의 확신도,
  "gold_insight": "재무/기술적 지표 기반 핵심 팩트 1줄 (수치 포함)",
  "silver_insight": "뉴스 감성/수급/매크로 기반 참고 의견 1줄"
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
